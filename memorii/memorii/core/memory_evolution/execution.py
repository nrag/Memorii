"""Production-owned execution events and derived work-state semantics.

Action events are immutable observations.  A work-state snapshot is a
deterministic projection over those events and is the only production object
that should answer continuation questions.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.models import ExtractedAction


class ActionEventType(StrEnum):
    START = "start"
    PROGRESS = "progress"
    RESUME = "resume"
    BLOCK = "block"
    COMPLETE = "complete"
    FAIL = "fail"
    ABANDON = "abandon"
    UNKNOWN = "unknown"


class WorkStateStatus(StrEnum):
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class ContinuationResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class ActionEvent(BaseModel):
    event_id: str
    event_type: ActionEventType = ActionEventType.UNKNOWN
    target_entity_ids: list[str] = Field(default_factory=list)
    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    scope_key: str = "global"
    event_time: datetime
    transaction_time: datetime | None = None
    explicit_status: WorkStateStatus = WorkStateStatus.UNKNOWN
    evidence_event_ids: list[str] = Field(default_factory=list)
    source_trust: int = Field(default=0, ge=0, le=5)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_timezones(self) -> ActionEvent:
        if self.event_time.tzinfo is None:
            raise ValueError("event_time must be timezone-aware")
        if self.transaction_time is not None and self.transaction_time.tzinfo is None:
            raise ValueError("transaction_time must be timezone-aware")
        return self


class WorkState(BaseModel):
    branch_id: str
    scope_key: str
    task_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    status: WorkStateStatus
    active: bool
    last_event_id: str
    last_event_type: ActionEventType
    last_progress_event_id: str | None = None
    last_progress_time: datetime | None = None
    evidence_event_ids: list[str] = Field(default_factory=list)
    state_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    ambiguity_reasons: list[str] = Field(default_factory=list)
    conflicting_event_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class WorkStateSnapshot(BaseModel):
    states: list[WorkState] = Field(default_factory=list)
    active_branch_ids: list[str] = Field(default_factory=list)
    suppressed_branch_ids: list[str] = Field(default_factory=list)
    ambiguous_branch_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ContinuationDecision(BaseModel):
    """Production-owned answer to an execution-continuation query."""

    status: ContinuationResolutionStatus
    branch_id: str | None = None
    scope_key: str | None = None
    action_event_id: str | None = None
    rationale: str
    candidate_branch_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


_STATUS_ALIASES: dict[str, WorkStateStatus] = {
    "start": WorkStateStatus.STARTED,
    "started": WorkStateStatus.STARTED,
    "in progress": WorkStateStatus.IN_PROGRESS,
    "in_progress": WorkStateStatus.IN_PROGRESS,
    "inprogress": WorkStateStatus.IN_PROGRESS,
    "progress": WorkStateStatus.IN_PROGRESS,
    "progressed": WorkStateStatus.IN_PROGRESS,
    "continue": WorkStateStatus.IN_PROGRESS,
    "continued": WorkStateStatus.IN_PROGRESS,
    "resume": WorkStateStatus.IN_PROGRESS,
    "resumed": WorkStateStatus.IN_PROGRESS,
    "reopen": WorkStateStatus.IN_PROGRESS,
    "reopened": WorkStateStatus.IN_PROGRESS,
    "blocked": WorkStateStatus.BLOCKED,
    "stuck": WorkStateStatus.BLOCKED,
    "complete": WorkStateStatus.COMPLETED,
    "completed": WorkStateStatus.COMPLETED,
    "done": WorkStateStatus.COMPLETED,
    "fail": WorkStateStatus.FAILED,
    "failed": WorkStateStatus.FAILED,
    "succeeded": WorkStateStatus.SUCCEEDED,
    "abandon": WorkStateStatus.ABANDONED,
    "abandoned": WorkStateStatus.ABANDONED,
    "drop": WorkStateStatus.ABANDONED,
    "dropped": WorkStateStatus.ABANDONED,
}


def normalize_work_state_status(value: str | WorkStateStatus) -> WorkStateStatus:
    if isinstance(value, WorkStateStatus):
        return value
    normalized = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    return _STATUS_ALIASES.get(normalized, WorkStateStatus.UNKNOWN)


def normalize_action_event_type(value: str | ActionEventType) -> ActionEventType:
    if isinstance(value, ActionEventType):
        return value
    normalized = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    if normalized in {"start", "started"}:
        return ActionEventType.START
    if normalized in {"progress", "in progress", "progressed", "continue", "continued"}:
        return ActionEventType.PROGRESS
    if normalized in {"resume", "resumed", "reopen", "reopened"}:
        return ActionEventType.RESUME
    if normalized in {"block", "blocked", "stuck"}:
        return ActionEventType.BLOCK
    if normalized in {"complete", "completed", "done", "succeeded", "success"}:
        return ActionEventType.COMPLETE
    if normalized in {"fail", "failed", "failure"}:
        return ActionEventType.FAIL
    if normalized in {"abandon", "abandoned", "drop", "dropped"}:
        return ActionEventType.ABANDON
    return ActionEventType.UNKNOWN


def status_for_action_event(event_type: ActionEventType) -> WorkStateStatus:
    return {
        ActionEventType.START: WorkStateStatus.STARTED,
        ActionEventType.PROGRESS: WorkStateStatus.IN_PROGRESS,
        ActionEventType.RESUME: WorkStateStatus.IN_PROGRESS,
        ActionEventType.BLOCK: WorkStateStatus.BLOCKED,
        ActionEventType.COMPLETE: WorkStateStatus.COMPLETED,
        ActionEventType.FAIL: WorkStateStatus.FAILED,
        ActionEventType.ABANDON: WorkStateStatus.ABANDONED,
    }.get(event_type, WorkStateStatus.UNKNOWN)


def action_event_from_extracted(action: ExtractedAction) -> ActionEvent:
    return ActionEvent(
        event_id=action.action_id,
        event_type=normalize_action_event_type(action.action_type),
        target_entity_ids=list(action.target_entity_ids),
        task_id=action.task_id,
        session_id=action.session_id,
        user_id=action.user_id,
        scope_key=action.scope_key,
        event_time=action.timestamp,
        explicit_status=normalize_work_state_status(action.status),
        evidence_event_ids=[span.source_id for span in action.evidence_spans],
    )


def reduce_work_states(events: Iterable[ActionEvent]) -> WorkStateSnapshot:
    grouped: dict[tuple[str, str, str | None, str | None, str | None], list[ActionEvent]] = defaultdict(list)
    for event in events:
        targets = event.target_entity_ids or [event.event_id]
        for target_id in targets:
            grouped[(target_id, event.scope_key, event.task_id, event.session_id, event.user_id)].append(event)

    states: list[WorkState] = []
    for (branch_id, scope_key, task_id, session_id, user_id), branch_events in sorted(
        grouped.items(), key=lambda item: tuple(value or "" for value in item[0])
    ):
        ordered = sorted(branch_events, key=_event_sort_key)
        last = ordered[-1]
        ambiguity_reasons: list[str] = []
        terminal_rank = _event_semantic_rank(last)
        terminal_events = [event for event in ordered if _event_semantic_rank(event) == terminal_rank]
        terminal_statuses = {_effective_event_status(event) for event in terminal_events}
        conflicting_event_ids: list[str] = []
        if len(terminal_statuses) > 1:
            status = WorkStateStatus.UNKNOWN
            ambiguity_reasons.append("simultaneous_contradictory_action_events")
            conflicting_event_ids = sorted(event.event_id for event in terminal_events)
        else:
            status = next(iter(terminal_statuses))
        inferred_status = status_for_action_event(last.event_type)
        if status == WorkStateStatus.UNKNOWN and not conflicting_event_ids:
            status = inferred_status
        elif not conflicting_event_ids and inferred_status not in {WorkStateStatus.UNKNOWN, status}:
            ambiguity_reasons.append("explicit_status_conflicts_with_event_type")
        progress_events = [
            event
            for event in ordered
            if event.explicit_status == WorkStateStatus.IN_PROGRESS
            or status_for_action_event(event.event_type) == WorkStateStatus.IN_PROGRESS
        ]
        evidence_event_ids = _ordered_unique(
            evidence_id
            for event in ordered
            for evidence_id in event.evidence_event_ids
        )
        states.append(
            WorkState(
                branch_id=branch_id,
                scope_key=scope_key,
                task_id=task_id,
                session_id=session_id,
                user_id=user_id,
                status=status,
                active=status in {WorkStateStatus.STARTED, WorkStateStatus.IN_PROGRESS},
                last_event_id=last.event_id,
                last_event_type=last.event_type,
                last_progress_event_id=progress_events[-1].event_id if progress_events else None,
                last_progress_time=progress_events[-1].event_time if progress_events else None,
                evidence_event_ids=evidence_event_ids,
                state_confidence=min(1.0, 0.5 + 0.1 * last.source_trust),
                ambiguity_reasons=ambiguity_reasons,
                conflicting_event_ids=conflicting_event_ids,
            )
        )

    active = [state for state in states if state.active]
    ambiguous = [state for state in states if state.ambiguity_reasons]
    return WorkStateSnapshot(
        states=states,
        active_branch_ids=[state.branch_id for state in active],
        suppressed_branch_ids=[state.branch_id for state in states if not state.active and not state.ambiguity_reasons],
        ambiguous_branch_ids=[state.branch_id for state in ambiguous],
    )


def resolve_continuation(
    snapshot: WorkStateSnapshot,
    actions: Iterable[ExtractedAction],
    *,
    requested_scope_key: str | None = None,
    requested_task_id: str | None = None,
    requested_session_id: str | None = None,
    requested_user_id: str | None = None,
    target_entity_ids: Iterable[str] = (),
) -> ContinuationDecision:
    """Resolve one continuation branch without guessing across peers.

    Scope and explicit entity constraints narrow the candidate set.  Progress
    outranks a bare start within the same branch.  Equally plausible branches
    remain ambiguous; a stable ID sort is never used as semantic evidence.
    """

    target_ids = {str(value) for value in target_entity_ids if value}
    states_by_branch = {
        (state.branch_id, state.scope_key, state.task_id, state.session_id, state.user_id): state
        for state in snapshot.states
        if state.active
    }
    candidates = [
        state
        for state in states_by_branch.values()
        if (not target_ids or state.branch_id in target_ids)
        and _matches_execution_context(
            state,
            requested_scope_key=requested_scope_key,
            requested_task_id=requested_task_id,
            requested_session_id=requested_session_id,
            requested_user_id=requested_user_id,
        )
    ]
    if not candidates:
        return ContinuationDecision(
            status=ContinuationResolutionStatus.NONE,
            rationale="no active continuation branch matches the requested scope and entity",
        )

    if requested_scope_key is not None:
        exact = [state for state in candidates if state.scope_key == requested_scope_key]
        if exact:
            candidates = exact

    for field_name, requested_value in (
        ("task_id", requested_task_id),
        ("session_id", requested_session_id),
        ("user_id", requested_user_id),
    ):
        if requested_value is None:
            continue
        exact = [state for state in candidates if getattr(state, field_name) == requested_value]
        if exact:
            candidates = exact

    if any(state.branch_id in snapshot.ambiguous_branch_ids for state in candidates):
        return ContinuationDecision(
            status=ContinuationResolutionStatus.AMBIGUOUS,
            rationale="one or more candidate branches have unresolved lifecycle ambiguity",
            candidate_branch_ids=sorted({state.branch_id for state in candidates}),
        )

    action_by_event_id = {action.action_id: action for action in actions}

    def rank(state: WorkState) -> tuple[int, datetime, int]:
        action = action_by_event_id.get(state.last_event_id)
        return (
            1 if state.status == WorkStateStatus.IN_PROGRESS else 0,
            state.last_progress_time or datetime.min.replace(tzinfo=UTC),
            1 if action is not None else 0,
        )

    best_rank = max(rank(state) for state in candidates)
    best = [state for state in candidates if rank(state) == best_rank]
    if len(best) != 1:
        return ContinuationDecision(
            status=ContinuationResolutionStatus.AMBIGUOUS,
            rationale="multiple active branches remain equally eligible",
            candidate_branch_ids=sorted({state.branch_id for state in best}),
        )
    selected = best[0]
    return ContinuationDecision(
        status=ContinuationResolutionStatus.RESOLVED,
        branch_id=selected.branch_id,
        scope_key=selected.scope_key,
        action_event_id=selected.last_event_id,
        rationale="selected the unique active branch after scope and progress filtering",
        candidate_branch_ids=[selected.branch_id],
    )


def _event_sort_key(event: ActionEvent) -> tuple[datetime, datetime, int, str]:
    return (
        event.event_time.astimezone(UTC),
        (event.transaction_time or datetime.min.replace(tzinfo=UTC)).astimezone(UTC),
        event.source_trust,
        event.event_id,
    )


def _event_semantic_rank(event: ActionEvent) -> tuple[datetime, datetime, int]:
    return _event_sort_key(event)[:3]


def _effective_event_status(event: ActionEvent) -> WorkStateStatus:
    return (
        event.explicit_status
        if event.explicit_status != WorkStateStatus.UNKNOWN
        else status_for_action_event(event.event_type)
    )


def _matches_execution_context(
    state: WorkState,
    *,
    requested_scope_key: str | None,
    requested_task_id: str | None,
    requested_session_id: str | None,
    requested_user_id: str | None,
) -> bool:
    if requested_scope_key is not None and state.scope_key not in {requested_scope_key, "global"}:
        return False
    for field_name, requested_value in (
        ("task_id", requested_task_id),
        ("session_id", requested_session_id),
        ("user_id", requested_user_id),
    ):
        if requested_value is not None and getattr(state, field_name) not in {requested_value, None}:
            return False
    return True


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
