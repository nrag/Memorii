"""Independent oracle reducer for execution checkpoints.

This module intentionally does not import production execution semantics.
The duplicate is a testing asset: agreement is evidence, not a shared
implementation guarantee.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.benchmark.memory_evolution_sim import LatentGraphScenario, OracleCheckpoint


class OracleWorkStateStatus(StrEnum):
    STARTED = "started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class OracleAction(BaseModel):
    claim_id: str
    branch_id: str
    status: OracleWorkStateStatus
    evidence_event_ids: list[str] = Field(default_factory=list)
    scope_key: str = "global"
    event_time: datetime | None = None

    model_config = ConfigDict(extra="forbid")


class OracleWorkState(BaseModel):
    branch_id: str
    status: OracleWorkStateStatus
    active: bool
    supporting_claim_ids: list[str] = Field(default_factory=list)
    supporting_event_ids: list[str] = Field(default_factory=list)
    scope_key: str = "global"

    model_config = ConfigDict(extra="forbid")


def reduce_oracle_work_states(actions: Iterable[OracleAction]) -> list[OracleWorkState]:
    latest: dict[str, OracleAction] = {}
    for action in actions:
        key = f"{action.scope_key}:{action.branch_id}"
        previous = latest.get(key)
        if previous is None or _oracle_time(action) >= _oracle_time(previous):
            latest[key] = action
    return [
        OracleWorkState(
            branch_id=branch_id,
            status=action.status,
            active=action.status in {OracleWorkStateStatus.STARTED, OracleWorkStateStatus.IN_PROGRESS},
                supporting_claim_ids=[action.claim_id],
                supporting_event_ids=list(action.evidence_event_ids),
                scope_key=action.scope_key,
        )
        for key, action in sorted(latest.items())
        for branch_id in [action.branch_id]
    ]


def build_oracle_execution_expectation(
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
) -> list[OracleWorkState]:
    actions: list[OracleAction] = []
    visible_event_ids = {
        observation.event_id
        for observation in scenario.observations
        if observation.timestamp <= checkpoint.timestamp
    }
    for claim in scenario.claims:
        if claim.claim_kind != "action_state" or claim.observability.value == "hidden":
            continue
        evidence_ids = [event_id for event_id in claim.evidence.source_event_ids if event_id in visible_event_ids]
        if not evidence_ids:
            continue
        action_time = claim.lifecycle.valid_from
        if action_time is not None and action_time > checkpoint.timestamp:
            continue
        actions.append(
            OracleAction(
                claim_id=claim.claim_id,
                branch_id=claim.subject.entity_id,
                status=_normalize_oracle_status(claim.object.value),
                evidence_event_ids=evidence_ids,
                scope_key=claim.scope.scope_key,
                event_time=action_time,
            )
        )
    return reduce_oracle_work_states(actions)


def _normalize_oracle_status(value: str) -> OracleWorkStateStatus:
    normalized = " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())
    return {
        "start": OracleWorkStateStatus.STARTED,
        "started": OracleWorkStateStatus.STARTED,
        "in progress": OracleWorkStateStatus.IN_PROGRESS,
        "progress": OracleWorkStateStatus.IN_PROGRESS,
        "progressed": OracleWorkStateStatus.IN_PROGRESS,
        "continue": OracleWorkStateStatus.IN_PROGRESS,
        "resumed": OracleWorkStateStatus.IN_PROGRESS,
        "reopened": OracleWorkStateStatus.IN_PROGRESS,
        "blocked": OracleWorkStateStatus.BLOCKED,
        "stuck": OracleWorkStateStatus.BLOCKED,
        "completed": OracleWorkStateStatus.COMPLETED,
        "done": OracleWorkStateStatus.COMPLETED,
        "failed": OracleWorkStateStatus.FAILED,
        "succeeded": OracleWorkStateStatus.SUCCEEDED,
        "abandoned": OracleWorkStateStatus.ABANDONED,
        "dropped": OracleWorkStateStatus.ABANDONED,
    }.get(normalized, OracleWorkStateStatus.UNKNOWN)


def _oracle_time(action: OracleAction) -> datetime:
    value = action.event_time
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    return value.astimezone(UTC)
