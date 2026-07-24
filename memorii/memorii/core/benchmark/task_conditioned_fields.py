"""Shared presence rules for task-conditioned benchmark output fields."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum


class TaskFieldPresencePolicy(StrEnum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


class TaskFieldPresenceViolation(StrEnum):
    REQUIRED_MISSING = "required_missing"
    FORBIDDEN_PRESENT = "forbidden_present"


def task_field_presence_violation(
    *,
    policy: TaskFieldPresencePolicy,
    item_count: int,
) -> TaskFieldPresenceViolation | None:
    """Return the single presence violation implied by a task policy."""

    if policy == TaskFieldPresencePolicy.REQUIRED and item_count == 0:
        return TaskFieldPresenceViolation.REQUIRED_MISSING
    if policy == TaskFieldPresencePolicy.FORBIDDEN and item_count > 0:
        return TaskFieldPresenceViolation.FORBIDDEN_PRESENT
    return None


def allowed_task_operations(operations: Iterable[str]) -> tuple[str, ...]:
    """Return the task's deterministic operation domain, including abstention."""

    return tuple(sorted({*operations, "abstain"}))


def task_operation_allowed(*, allowed_operations: Iterable[str], operation: str) -> bool:
    """Return whether an operation belongs to the task-conditioned domain."""

    return operation in allowed_task_operations(allowed_operations)
